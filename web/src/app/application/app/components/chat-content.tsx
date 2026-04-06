'use client';

import { AppContext, ChatContentContext, SelectedSkill, ContextMetricsProvider } from '@/contexts';
import { ChartData, ChatHistoryResponse, UserChatContent} from '@/types/chat';
import { useContext, useState, useRef, useCallback, useEffect } from 'react';
import { Layout } from 'antd';
import ChatContentContainer from '@/components/chat/chat-content-container';
import useChat from '@/hooks/use-chat';
import { getInitMessage, transformFileMarkDown, transformFileUrl } from '@/utils';
const { Content } = Layout;

function ChatContent() {
  const { appInfo, setCollapsed, collapsed, refreshAppInfo, chatId } = useContext(AppContext);
  const [history, setHistory] = useState<ChatHistoryResponse>([]);
  const [chartsData] = useState<Array<ChartData>>();
  const [replyLoading, setReplyLoading] = useState<boolean>(false);
  const [canAbort, setCanAbort] = useState<boolean>(false);
  const [agent, setAgent] = useState<string>('');
  const [temperatureValue, setTemperatureValue] = useState<number>(0.6);
  const [maxNewTokensValue, setMaxNewTokensValue] = useState<number>(4000);
  const [resourceValue, setResourceValue] = useState<any>();
  const [chatInParams, setChatInParams] = useState<Array<{
    param_type: string;
    param_value: string;
    sub_type: string;
  }>>([]);
  const [modelValue, setModelValue] = useState<string>('');
  const [selectedSkills, setSelectedSkills] = useState<SelectedSkill[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [currentDialogue] = useState<any>(null);

  const { chat, ctrl } = useChat({
    app_code: appInfo.app_code || '',
    agent_version: appInfo.agent_version || 'v1',
  });
    const order = useRef<number>(1);

  // 会话提问
  const handleChat = useCallback(
    (content: UserChatContent, data?: Record<string, unknown>) => {
      return new Promise<void>(resolve => {
        const initMessage = getInitMessage();
        const ctrl = new AbortController();
         setTimeout(() => {
            setCollapsed(true);
         }, 50);
        setReplyLoading(true);
        if (history && history.length > 0) {
          const viewList = history?.filter(item => item.role === 'view');
          const humanList = history?.filter(item => item.role === 'human');
          order.current = (viewList[viewList.length - 1]?.order || humanList[humanList.length - 1]?.order) + 1;
        }
        let formattedDisplayContent: string = '';
        if (typeof content === 'string') {
          formattedDisplayContent = content;
        } else {
          // Extract content items for display formatting
          const contentItems = content.content || [];
          const textItems = contentItems.filter(item => item.type === 'text');
          const mediaItems = contentItems.filter(item => item.type !== 'text');
          // Format for display in the UI - extract text for main message
          if (textItems.length > 0) {
            // Use the text content for the main message display
            formattedDisplayContent = textItems.map(item => item.text).join(' ');
          }

          // Format media items for display (using markdown)
          const mediaMarkdown = mediaItems
            .map(item => {
              if (item.type === 'image_url') {
                const originalUrl = item.image_url?.url || '';
                // Transform the URL to a service URL that can be displayed
                const displayUrl = transformFileUrl(originalUrl);
                const fileName = item.image_url?.fileName || 'image';
                return `\n![${fileName}](${displayUrl})`;
              } else if (item.type === 'video') {
                const originalUrl = item.video || '';
                const displayUrl = transformFileUrl(originalUrl);
                return `\n[Video](${displayUrl})`;
              } else  {
                const fileMarkdown = transformFileMarkDown(item.file_url);
                return `\n${fileMarkdown}`;
              }
            })
            .join('\n');

          // Combine text and media markup
          if (mediaMarkdown) {
            formattedDisplayContent = formattedDisplayContent + '\n' + mediaMarkdown;
          }
        }

        const tempHistory: ChatHistoryResponse = [
          ...(initMessage && initMessage.id === chatId ? [] : history),
          {
            role: 'human',
            context: formattedDisplayContent,
            model_name: (data as any)?.model_name || modelValue,
            order: order.current,
            time_stamp: 0,
          },
          {
            role: 'view',
            context: '',
            model_name: (data as any)?.model_name || modelValue,
            order: order.current,
            time_stamp: 0,
            thinking: true,
          },
        ];
        const index = tempHistory.length - 1;
        setHistory([...tempHistory]);
        chat({
          data: {
            user_input: content,
            team_mode: appInfo?.team_mode || '',
            app_config_code: appInfo?.config_code || '',
            conv_uid: chatId,
            ext_info: {
              vis_render: appInfo?.layout?.chat_layout?.name || '',
              incremental: appInfo?.layout?.chat_layout?.incremental || false,
            },
            ...data,
          },
          ctrl, 
          onMessage: message => {
            setCanAbort(true);
            if (message) {
              if (data?.incremental) {
                // VisParser.update() 返回的是完整合并状态，直接替换而非追加
                tempHistory[index].context = message;
                tempHistory[index].thinking = false;
              } else {
                tempHistory[index].context = message;
                tempHistory[index].thinking = false;
              }
              setHistory([...tempHistory]);
            }
          },
          onDone: () => {
            setReplyLoading(false);
            setCanAbort(false);
            resolve();
          },
          onClose: () => {
            setReplyLoading(false);
            setCanAbort(false);
            resolve();
          },
          onError: message => {
            setReplyLoading(false);
            setCanAbort(false);
            tempHistory[index].context = message;
            tempHistory[index].thinking = false;
            setHistory([...tempHistory]);
            resolve();
          },
        });
      });
    },

    [history, modelValue, chat, appInfo, chatId],
  );
  // 调试页面无法刷新会话列表，先留空
  const refreshHistory = () => {
    // Implement history refresh logic here
  };

  useEffect(() => {
    if(appInfo?.layout?.chat_in_layout?.length){
      const layout =  appInfo?.layout?.chat_in_layout;
      const temp = layout.find((item: { param_type: string; }) => item.param_type === 'temperature');
      const token = layout.find((item: { param_type: string; }) => item.param_type === 'max_new_tokens');
      const resource = layout.find((item: { param_type: string; }) => item.param_type === 'resource');
      const model = layout.find((item: { param_type: string; }) => item.param_type === 'model');
      setTemperatureValue(Number(temp?.param_default_value) || 0.6);
      setMaxNewTokensValue(Number(token?.param_default_value) || 4000);
      setModelValue(model?.param_default_value || '');
      setResourceValue(resource?.param_default_value || null);
      const chatInParam = [
          ...(temp ? [{
            param_type: 'temperature',
            param_value: JSON.stringify(temp?.param_default_value),
            sub_type: temp?.sub_type,
          }] : []),
           ...(token ? [{
            param_type: 'max_new_tokens',
            param_value: JSON.stringify(token?.param_default_value),
            sub_type: token?.sub_type,
          }] : []),
           ...(resource ? [{
            param_type: 'resource',
            param_value: JSON.stringify(resource?.param_default_value),
            sub_type: resource?.sub_type,
          }] : []),
           ...(model ? [{
            param_type: 'model',
            param_value: JSON.stringify(model?.param_default_value),
            sub_type: model?.sub_type,
          }] : []),
        ];
        setChatInParams(chatInParam);
    }
  }, [appInfo?.layout?.chat_in_layout]);

  return (
    <ContextMetricsProvider convId={chatId}>
      <ChatContentContext.Provider
        value={{
          history,
          replyLoading,
          scrollRef,
          canAbort,
          chartsData: chartsData || [],
          agent,
          currentDialogue,
          appInfo,
          temperatureValue,
          maxNewTokensValue,
          resourceValue,
          modelValue,
          selectedSkills,
          setModelValue,
          setResourceValue,
          setSelectedSkills,
          setTemperatureValue,
          setMaxNewTokensValue,
          setChatInParams,
          chatInParams,
          setAgent,
          setCanAbort,
          setReplyLoading,
          handleChat,
          refreshHistory,
          refreshAppInfo: refreshAppInfo ?? (() => {}),
          setHistory,
          isShowDetail: collapsed,
          isDebug: true,
          setAppInfo: () => {},
          refreshDialogList: () => {}
        }}
      >
        <div className="flex-1 flex flex-col h-full relative bg-transparent">
          <div className="flex-1 bg-transparent overflow-hidden">
            <Content className='flex flex-col flex-1 h-full'>
              <ChatContentContainer ref={scrollRef} ctrl={ctrl} />
            </Content>
          </div>
        </div>
      </ChatContentContext.Provider>
    </ContextMetricsProvider>
  );
}

export default ChatContent;
