/**
 * Unified Chat Service - 统一聊天服务
 * 根据 App 配置自动切换 V1/V2 后端
 */
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { getUserId } from '@/utils';
import { HEADER_USER_ID_KEY } from '@/utils/constants/index';

export type AgentVersion = 'v1' | 'v2';

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

export interface V2StreamChunk {
  type: 'response' | 'thinking' | 'tool_call' | 'error';
  content: string;
  metadata: Record<string, any>;
  is_final: boolean;
}

// V1 Chat
async function chatV1(config: ChatConfig, callbacks: any, controller: AbortController) {
  const params = { ...config };
  await fetchEventSource(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/v1/chat/completions`, {
    method: 'POST',
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

// V2 Chat
async function chatV2(config: ChatConfig, callbacks: any, controller: AbortController) {
  const requestBody: Record<string, any> = {
    user_input: config.user_input,
    conv_uid: config.conv_uid,
    session_id: config.conv_uid,
    app_code: config.app_code,
    model_name: config.model_name,
    select_param: config.select_param,
    chat_in_params: config.chat_in_params,
    temperature: config.temperature,
    max_new_tokens: config.max_new_tokens,
    work_mode: config.work_mode || 'simple',
    stream: true,
    ext_info: config.ext_info || {},
    user_id: getUserId(),
  };

  if (config.messages) {
    requestBody.messages = config.messages;
  }

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/v2/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      [HEADER_USER_ID_KEY]: getUserId() ?? '',
    },
    body: JSON.stringify(requestBody),
    signal: controller.signal,
  });
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    for (const line of buffer.split('\n')) {
      if (line.startsWith('data: ')) {
        try {
          const chunk = JSON.parse(line.slice(6)) as V2StreamChunk;
          if (chunk.type === 'response') callbacks.onMessage(chunk.content);
          else callbacks.onChunk?.(chunk);
          if (chunk.is_final) callbacks.onDone();
        } catch {}
      }
    }
    buffer = '';
  }
}

export class UnifiedChatService {
  private controller: AbortController | null = null;

  async sendMessage(config: ChatConfig, callbacks: any) {
    this.controller = new AbortController();
    const version = config.agent_version || (config.app_code?.startsWith('v2_') ? 'v2' : 'v1');
    if (version === 'v2') await chatV2(config, callbacks, this.controller);
    else await chatV1(config, callbacks, this.controller);
  }

  abort() { this.controller?.abort(); this.controller = null; }
}

let service: UnifiedChatService | null = null;
export const getChatService = () => service || (service = new UnifiedChatService());
