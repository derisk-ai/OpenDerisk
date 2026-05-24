import { ins as axios } from '@/client/api';

const API_BASE = '/api/v1';

export interface PermissionRequest {
  id: number;
  user_id: number;
  user_name?: string;
  user_email?: string;
  request_type: 'role_assign' | 'permission_grant' | 'account_activation';
  role_id?: number;
  role_name?: string;
  resource_type?: string;
  resource_id?: string;
  action?: string;
  reason?: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  reviewer_id?: number;
  reviewer_name?: string;
  review_comment?: string;
  gmt_create: string;
  gmt_modify: string;
  gmt_review?: string;
}

export interface CreatePermissionRequestParams {
  request_type: 'role_assign' | 'permission_grant' | 'account_activation';
  role_id?: number;
  resource_type?: string;
  resource_id?: string;
  action?: string;
  reason?: string;
}

export interface PermissionRequestListResult {
  items: PermissionRequest[];
  total: number;
  page: number;
  page_size: number;
}

class PermissionRequestService {
  async createRequest(params: CreatePermissionRequestParams): Promise<PermissionRequest> {
    const res = await axios.post(`${API_BASE}/permissions/requests`, params);
    return res.data.data as PermissionRequest;
  }

  async listRequests(params?: {
    status?: string;
    user_id?: number;
    reviewer_id?: number;
    request_type?: string;
    page?: number;
    page_size?: number;
  }): Promise<PermissionRequestListResult> {
    const res = await axios.get(`${API_BASE}/permissions/requests`, { params });
    return res.data.data as PermissionRequestListResult;
  }

  async getMyRequests(params?: {
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<PermissionRequestListResult> {
    const res = await axios.get(`${API_BASE}/permissions/requests/my`, { params });
    return res.data.data as PermissionRequestListResult;
  }

  async getRequest(requestId: number): Promise<PermissionRequest> {
    const res = await axios.get(`${API_BASE}/permissions/requests/${requestId}`);
    return res.data.data as PermissionRequest;
  }

  async approveRequest(requestId: number, reviewComment?: string): Promise<PermissionRequest> {
    const res = await axios.post(`${API_BASE}/permissions/requests/${requestId}/approve`, {
      review_comment: reviewComment,
    });
    return res.data.data as PermissionRequest;
  }

  async rejectRequest(requestId: number, reviewComment?: string): Promise<PermissionRequest> {
    const res = await axios.post(`${API_BASE}/permissions/requests/${requestId}/reject`, {
      review_comment: reviewComment,
    });
    return res.data.data as PermissionRequest;
  }

  async cancelRequest(requestId: number): Promise<PermissionRequest> {
    const res = await axios.post(`${API_BASE}/permissions/requests/${requestId}/cancel`);
    return res.data.data as PermissionRequest;
  }

  async getPendingCount(): Promise<number> {
    const res = await axios.get(`${API_BASE}/permissions/requests/pending-count`);
    return res.data.data.count as number;
  }
}

export const permissionRequestService = new PermissionRequestService();