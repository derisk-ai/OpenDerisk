/**
 * Unified Chat Service - 统一聊天服务
 */
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { getUserId } from '@/utils';
import { HEADER_USER_ID_KEY } from '@/utils/constants/index';

export type AgentVersion = 'v1';

export interface ChatConfig {
  app_code: string;
  agent_version?: AgentVersion;
  conv_uid?: string;
  user_input: string;
  model_name?: string;
  select_param?: any;
  chat_in_params?: Array<{ param_type: string; sub_type?: string; param_value: string }>;
  temperature?: number;
  max_new_tokens?: number;
  work_mode?: 'simple' | 'quick' | 'background' | 'async';
  messages?: Array<{ role: string; content: any }>;
  ext_info?: Record<string, any>;
  [key: string]: any;
}

// V1 Chat
async function chatV1(config: ChatConfig, callbacks: any, controller: AbortController) {
  const params = { ...config };
  await fetchEventSource(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/v1/chat/completions`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', [HEADER_USER_ID_KEY]: getUserId() ?? '' },
    body: JSON.stringify(params),
    signal: controller.signal,
    openWhenHidden: true,
    onmessage: (event) => {
      let msg = event.data;
      try { msg = JSON.parse(msg).vis || msg; } catch {}
      if (msg === '[DONE]') callbacks.onDone();
      else if (msg?.startsWith('[ERROR]')) callbacks.onError(msg.replace('[ERROR]', ''));
      else callbacks.onMessage(msg);
    },
    onclose: callbacks.onClose,
    onerror: (err) => { throw err; },
  });
}

export class UnifiedChatService {
  private controller: AbortController | null = null;

  async sendMessage(config: ChatConfig, callbacks: any) {
    this.controller = new AbortController();
    await chatV1(config, callbacks, this.controller);
  }

  abort() { this.controller?.abort(); this.controller = null; }
}

let service: UnifiedChatService | null = null;
export const getChatService = () => service || (service = new UnifiedChatService());
