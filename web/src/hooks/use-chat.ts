import { ChatContentContext, ChatContext } from '@/contexts';
import i18n from '@/app/i18n';
import { getUserId } from '@/utils';
import { HEADER_USER_ID_KEY } from '@/utils/constants/index';
import { EventStreamContentType, fetchEventSource } from '@microsoft/fetch-event-source';
import { message } from 'antd';
import { useCallback, useState } from 'react';
import { VisParser } from '@/utils/parse-vis';

type Props = {
  queryAgentURL?: string;
  app_code?: string;
  agent_version?: 'v1' | 'v2';
};

type ChatParams = {
  chatId?: string;
  ctrl?: AbortController;
  data?: any;
  query?: Record<string, string>;
  onMessage: (message: string) => void;
  onClose?: () => void;
  onDone?: () => void;
  onError?: (content: string, error?: Error) => void;
};

type V2StreamChunk = {
  type: 'response' | 'thinking' | 'tool_call' | 'error';
  content: string;
  metadata: Record<string, any>;
  is_final: boolean;
};

export function parseChunkData(
  preText: string,
  preMidMsg: { nodeId: string; text: string },
  data: any,
  visParser: VisParser,
) {

  const answerText = preText || '';
  const midMsgObject = preMidMsg || {
    nodeId: '',
    text: '',
  }; 
  // 中间态消息, 如果下次的nodeId相同，追加；不同，则覆盖
  const answer: string = data.vis;
  midMsgObject.text = visParser.update(answer);
  return { answerText, midMsgObject };
}

const useChat = ({ queryAgentURL = '/api/v1/chat/completions', app_code, agent_version = 'v1' }: Props) => {
  const [ctrl, setCtrl] = useState<AbortController>({} as AbortController);
  
  const chatV2 = useCallback(async ({ data, onMessage, onClose, onDone, onError, ctrl }: ChatParams) => {
    let messageText = '';
    if (typeof data?.user_input === 'string') {
      messageText = data.user_input;
    } else if (data?.user_input?.content) {
      const textItems = data.user_input.content.filter((item: any) => item.type === 'text');
      messageText = textItems.map((item: any) => item.text).join(' ');
    }

    if (!messageText && !data?.doc_id) {
      message.warning(i18n.t('no_context_tip'));
      return;
    }

    const requestBody: Record<string, any> = {
      message: messageText,
      user_input: data?.user_input,
      conv_uid: data?.conv_uid,
      session_id: data?.conv_uid,
      app_code: app_code,
      agent_name: app_code,
      model_name: data?.model_name,
      select_param: data?.select_param,
      chat_in_params: data?.chat_in_params,
      temperature: data?.temperature,
      max_new_tokens: data?.max_new_tokens,
      work_mode: data?.work_mode || 'simple',
      stream: true,
      user_id: getUserId(),
      ext_info: data?.ext_info || {},
    };

    if (data?.messages) {
      requestBody.messages = data.messages;
    }

    const visParser = new VisParser();

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}/api/v2/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          [HEADER_USER_ID_KEY]: getUserId() ?? '',
        },
        body: JSON.stringify(requestBody),
        signal: ctrl?.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              const vis = data.vis;
              
              if (typeof vis === 'string') {
                if (vis === '[DONE]') {
                  onDone?.();
                } else if (vis.startsWith('[ERROR]')) {
                  onError?.(vis.replace('[ERROR]', '').replace('[/ERROR]', ''));
                } else {
                  const merged = visParser.update(vis);
                  onMessage?.(merged);
                }
              } else if (typeof vis === 'object' && vis !== null) {
                // Handle metadata and other object messages
                if (vis.type === 'metadata' || vis.type === 'interrupt') {
                  onMessage?.(vis);
                } else if (vis.type === 'error') {
                  onError?.(vis.content || '对话发生错误');
                } else {
                  onMessage?.(vis);
                }
              }
            } catch {}
          }
        }
      }
      onDone?.();
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        onError?.('Request failed', err);
      }
    }
  }, [app_code]);

  const chatV1 = useCallback(
    async ({ data, onMessage, onClose, onDone, onError, ctrl }: ChatParams) => {
      ctrl && setCtrl(ctrl);
      if (!data?.user_input && !data?.doc_id) {
        message.warning(i18n.t('no_context_tip'));
        return;
      }

      const params = { ...data, app_code };
      const isIncremental = data?.ext_info?.incremental;
      const answerText = "";
      let midMsgObject = { nodeId: "", text: "" };
      const visParser = new VisParser();
      
      try {
        await fetchEventSource(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ''}${queryAgentURL}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            [HEADER_USER_ID_KEY]: getUserId() ?? '',
          },
          body: JSON.stringify(params),
          signal: ctrl ? ctrl.signal : null,
          openWhenHidden: true,
          async onopen(response) {
            if (response.ok && response.headers.get('content-type') === EventStreamContentType) return;
            if (response.headers.get('content-type') === 'application/json') {
              response.json().then(data => { onMessage?.(data); onDone?.(); ctrl && ctrl.abort(); });
            }
          },
          onclose() { ctrl && ctrl.abort(); onClose?.(); },
          onerror(err) { console.error('err', err); throw new Error(err); },
          onmessage: event => {
            let message = event.data;
            try {
              const parsedData = JSON.parse(message);
              
              // Check if it's a metadata or interrupt message first
              if (parsedData?.vis && typeof parsedData.vis === 'object') {
                const vis = parsedData.vis;
                if (vis.type === 'metadata' || vis.type === 'interrupt') {
                  onMessage?.(vis);
                  return;
                } else if (vis.type === 'error') {
                  onError?.(vis.content || '对话发生错误');
                  return;
                }
              }
              
              if (!isIncremental) {
                message = parsedData.vis;
              } else {
                const { midMsgObject: newMidMsgObject } = parseChunkData(answerText, midMsgObject, parsedData, visParser);
                midMsgObject = newMidMsgObject;
                message = midMsgObject.text;
              }
            } catch { message = message.replaceAll('\\n', '\n'); }
            if (typeof message === 'string') {
              if (message === '[DONE]') onDone?.();
              else if (message?.startsWith('[ERROR]')) onError?.(message?.replace('[ERROR]', ''));
              else onMessage?.(message);
            } else if (typeof message === 'object' && message !== null) {
              // Handle other object messages
              onMessage?.(message);
            }
          },
        });
      } catch (err) {
        ctrl && ctrl.abort();
        onError?.('Sorry, We meet some error, please try again later.', err as Error);
      }
    },
    [queryAgentURL, app_code],
  );

  const chat = useCallback(
    async (params: ChatParams) => {
      const version = params.data?.agent_version || agent_version;
      if (version === 'v2') return chatV2(params);
      return chatV1(params);
    },
    [agent_version, chatV1, chatV2],
  );

  return { chat, ctrl };
};

export default useChat;
