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
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/v2/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: config.user_input, session_id: config.conv_uid, agent_name: config.app_code }),
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
