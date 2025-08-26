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

export function parseChunkData(
  preText: string,
  preMidMsg: { nodeId: string; text: string },
  data: any,
  visParser: VisParser,
) {

  let answerText = preText || '';
  let midMsgObject = preMidMsg || {
    nodeId: '',
    text: '',
  }; 
  // 中间态消息, 如果下次的nodeId相同，追加；不同，则覆盖
  const answer: string = data.vis;
  midMsgObject.text = visParser.update(answer);
  return { answerText, midMsgObject };
}

const useChat = ({ queryAgentURL = '/api/v1/chat/completions', app_code }: Props) => {
  const [ctrl, setCtrl] = useState<AbortController>({} as AbortController);
  const chat = useCallback(
    async ({ data, onMessage, onClose, onDone, onError, ctrl }: ChatParams) => {
      ctrl && setCtrl(ctrl);
      if (!data?.user_input && !data?.doc_id) {
        message.warning(i18n.t('no_context_tip'));
        return;
      }

      const params = {
        ...data,
        app_code    
      };

      const isIncremental = data?.ext_info?.incremental;
      let answerText = "";
      let midMsgObject = {
        nodeId: "",
        text: "",
      }; 
      
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
            if (response.ok && response.headers.get('content-type') === EventStreamContentType) {
              return;
            }
            if (response.headers.get('content-type') === 'application/json') {
              response.json().then(data => {
                onMessage?.(data);
                onDone?.();
                ctrl && ctrl.abort();
              });
            }
          },
          onclose() {
            ctrl && ctrl.abort();
            onClose?.();
          },
          onerror(err) {
             console.log('err', err);
            throw new Error(err);
          },
          onmessage: event => {
            let message = event.data;
            try {
              if (!isIncremental) {
                message = JSON.parse(message).vis;
              } else {
                const { answerText: newAnswerText, midMsgObject: newMidMsgObject } = parseChunkData(
                  answerText,
                  midMsgObject,
                  JSON.parse(message),
                  visParser,
                );
                answerText = newAnswerText;
                message = newMidMsgObject.text;
              }
             
            } catch {
              message.replaceAll('\\n', '\n');
            }
            if (typeof message === 'string') {
              if (message === '[DONE]') {
                onDone?.();
              } else if (message?.startsWith('[ERROR]')) {
                onError?.(message?.replace('[ERROR]', ''));
              } else {
                onMessage?.(message);
              }
            } else {
              onMessage?.(message);
              onDone?.();
            }
          },
        });
      } catch (err) {
        ctrl && ctrl.abort();
        onError?.('Sorry, We meet some error, please try agin later.', err as Error);
      }
    },
    [queryAgentURL, app_code],
  );
  return { chat, ctrl };
};

export default useChat;
