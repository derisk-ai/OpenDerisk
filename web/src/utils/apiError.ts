import axios from 'axios';

/** Extract human-readable message from axios / API error bodies (FastAPI detail, derisk err_msg, etc.). */
export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined;
    if (data && typeof data === 'object') {
      const errMsg = data.err_msg;
      if (typeof errMsg === 'string' && errMsg.trim()) return errMsg.trim();
      const detail = data.detail;
      if (typeof detail === 'string' && detail.trim()) return detail.trim();
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string };
        if (typeof first?.msg === 'string') return first.msg;
      }
      const msg = data.message;
      if (typeof msg === 'string' && msg.trim()) return msg.trim();
    }
    if (error.response?.status) {
      return `${error.message} (HTTP ${error.response.status})`;
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}

export function isHttpStatus(error: unknown, status: number): boolean {
  return axios.isAxiosError(error) && error.response?.status === status;
}
