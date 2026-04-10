"use client"
import { apiInterceptors, getAppInfo, getChatHistory, getDialogueList } from '@/client/api';
import { ChartData, ChatHistoryResponse, IChatDialogueSchema, UserChatContent } from '@/types/chat';
import { IApp } from '@/types/app';
import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useAsyncEffect, useDebounceFn, useRequest } from 'ahooks';
import useChat from '@/hooks/use-chat';
import useChatPolling from '@/hooks/use-chat-polling';
import ChatContentContainer from '@/components/chat/chat-content-container';
import { getInitMessage, transformFileMarkDown, transformFileUrl } from '@/utils';
import { STORAGE_INIT_MESSAGE_KET } from '@/utils/constants/storage';
import { Flex, Layout } from 'antd';
import ChatPageSkeleton from '@/components/chat/content/chat-page-skeleton';
import { useSearchParams } from 'next/navigation';
import { ChatContentContext, SelectedSkill, ContextMetricsProvider } from '@/contexts';
import HomeChat from '@/components/chat/content/home-chat';
import { useTranslation } from 'react-i18next';

const { Content } = Layout;

export default function Chat() {
  const { t } = useTranslation();

  const searchParams = useSearchParams();
  const chatId = (searchParams?.get('conv_uid') || searchParams?.get('chatId')) ?? '';
  const app_code = searchParams?.get('app_code') ?? '';
  const modelName = searchParams?.get('model') ?? '';
  const knowledgeId = searchParams?.get('knowledge') ?? '';
  const scrollRef = useRef<HTMLDivElement>(null);
  const order = useRef<number>(1);
  const [history, setHistory] = useState<ChatHistoryResponse>([]);
  const [chartsData] = useState<Array<ChartData>>();
  const [replyLoading, setReplyLoading] = useState<boolean>(false);
  const [canAbort, setCanAbort] = useState<boolean>(false);
  const [agent, setAgent] = useState<string>('');
  const [appInfo, setAppInfo] = useState<IApp>({} as IApp);
  const [temperatureValue, setTemperatureValue] = useState<number>(0.6);
  const [maxNewTokensValue, setMaxNewTokensValue] = useState<number>(4000);
  const [resourceValue, setResourceValue] = useState<any>();
  const [modelValue, setModelValue] = useState<string>('');
  const [isShowDetail, setIsShowDetail] = useState<boolean>(true);
  const [chatInParams, setChatInParams] = useState<{ param_type: string; param_value: string; sub_type: string; }[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<SelectedSkill[]>([]);
  const [currentConvSessionId, setCurrentConvSessionId] = useState<string>(chatId);
  const [sseActive, setSseActive] = useState(false);
  const chatInputRef = useRef<any>(null);
  const { chat, ctrl } = useChat({
    app_code: app_code || '',
  });

  // 是否是默认小助手（必须在 useChatPolling 之前定义）
  const isChatDefault = useMemo(() => {
    return !chatId;
  }, [chatId]);

  // 轮询恢复：重新打开运行中对话时，降级为轮询模式获取 vis_final
  const [isPollingMode, setIsPollingMode] = useState(false);
  const { isPolling, data: pollingData, stopPolling } = useChatPolling({
    convId: chatId || null,
    enabled: !isChatDefault && !sseActive,
    interval: 2500,
    onComplete: () => {
      setIsPollingMode(false);
      setReplyLoading(false);
      setCanAbort(false);
      refreshHistory();
    },
  });

  // 轮询模式：将 vis_final 写入 history 驱动渲染
  useEffect(() => {
    if (!pollingData?.vis_final || !isPolling) return;

    if (!isPollingMode) {
      setIsPollingMode(true);
      setReplyLoading(true);
      setCanAbort(true);
    }

    setHistory(prev => {
      const updated = [...prev];
      const lastViewIndex = updated.map(m => m.role).lastIndexOf('view');

      if (lastViewIndex >= 0) {
        updated[lastViewIndex] = {
          ...updated[lastViewIndex],
          context: pollingData.vis_final,
          thinking: false,
        };
      } else if (updated.length > 0) {
        updated.push({
          role: 'view',
          context: pollingData.vis_final,
          order: updated[updated.length - 1]?.order || 0,
          time_stamp: 0,
          model_name: '',
          thinking: false,
        });
      }
      return updated;
    });
  }, [pollingData, isPolling]);

  useEffect(() => {
    if(appInfo?.layout?.chat_in_layout?.length){
      const layout =  appInfo?.layout?.chat_in_layout;
      const temp = layout.find((item: { param_type: string; }) => item.param_type === 'temperature');
      const token = layout.find((item: { param_type: string; }) => item.param_type === 'max_new_tokens');
      const resource = layout.find((item: { param_type: string; }) => item.param_type === 'resource');
      const model = layout.find((item: { param_type: string; }) => item.param_type === 'model');
      setTemperatureValue(Number(temp?.param_default_value) || 0.6);
      setMaxNewTokensValue(Number(token?.param_default_value) || 4000);
      setModelValue(modelName || model?.param_default_value || '');
      setResourceValue(knowledgeId || resource?.param_default_value || null);

      const chatInParam = [
          ...(temp ? [{
            param_type: 'temperature',
            param_value: typeof temp?.param_default_value === 'string'
              ? temp?.param_default_value
              : JSON.stringify(temp?.param_default_value),
            sub_type: temp?.sub_type,
          }] : []),
           ...(token ? [{
            param_type: 'max_new_tokens',
            param_value: typeof token?.param_default_value === 'string'
              ? token?.param_default_value
              : JSON.stringify(token?.param_default_value),
            sub_type: token?.sub_type,
          }] : []),
           ...(resource ? [{
            param_type: 'resource',
            param_value: typeof resource?.param_default_value === 'string'
              ? (knowledgeId || resource?.param_default_value)
              : JSON.stringify(knowledgeId || resource?.param_default_value),
            sub_type: resource?.sub_type,
          }] : []),
           ...(model ? [{
            param_type: 'model',
            param_value: typeof model?.param_default_value === 'string'
              ? (modelName || model?.param_default_value)
              : JSON.stringify(modelName || model?.param_default_value),
            sub_type: model?.sub_type,
          }] : []),
        ]
        setChatInParams(chatInParam);
    }
  }, [appInfo?.layout?.chat_in_layout, modelName]);

  // 获取会话列表
  const {
    data: dialogueList = [],
    refresh: refreshDialogList,
    loading: listLoading,
  } = useRequest(async () => {
    return await apiInterceptors(getDialogueList());
  }, {
    pollingInterval: isPolling ? 5000 : undefined,
  });

  // 获取应用详情
  const { run: queryAppInfo, refresh: refreshAppInfo, loading: appInfoLoading } = useRequest(
    async () =>
      await apiInterceptors(
        getAppInfo({
          app_code: app_code,
          building_mode: false
        }),
      ),
    {
      manual: true,
      onSuccess: data => {
        const [, res] = data;
        setAppInfo(res || ({} as IApp));
      },
    },
  );

  // 列表当前活跃对话
  const currentDialogue = useMemo(() => {
    const [, list] = dialogueList;
    return list?.find(item => item.conv_uid === chatId) || ({} as IChatDialogueSchema);
  }, [chatId, dialogueList]);

  useEffect(() => {
    if (!isChatDefault) {
      queryAppInfo();
    }
  }, [chatId, isChatDefault, queryAppInfo, app_code]);

  // 获取会话历史记录
  const {
    run: getHistory,
    loading: historyLoading,
    refresh: refreshHistory,
  } = useRequest(async () => await apiInterceptors(getChatHistory(chatId)), {
    manual: true,
    onSuccess: data => {
      const [, res] = data;
      const viewList = res?.filter(item => item.role === 'view');
      if (viewList && viewList.length > 0) {
        order.current = viewList[viewList.length - 1].order + 1;
      }
      setHistory(res || []);
    },
  });

  // 会话提问
  const handleChat = useCallback(
    (content: UserChatContent, data?: Record<string, unknown>) => {
      return new Promise<void>(resolve => {
        // 退出轮询模式，SSE 接管
        if (isPollingMode) {
          setIsPollingMode(false);
          stopPolling();
        }
        const initMessage = getInitMessage();
        const ctrl = new AbortController();
        setSseActive(true);
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
              } else {
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
            agent_version: appInfo?.agent_version || 'v1',
            ext_info: {
              vis_render: appInfo?.layout?.chat_layout?.name || '',
              incremental: appInfo?.layout?.chat_layout?.incremental || false,
            },
            ...data,
          },
          ctrl, 
          chatId,
          onMessage: message => {
            setCanAbort(true);
            if (message) {
              // Check if message is metadata containing conv_session_id
              if (typeof message === 'object' && message.type === 'metadata') {
                if (message.conv_session_id) {
                  setCurrentConvSessionId(message.conv_session_id);
                }
                return;
              }
              // Check if message is interrupt notification
              if (typeof message === 'object' && message.type === 'interrupt') {
                // Handle interrupt - just acknowledge it
                return;
              }
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
            setSseActive(false);
            setReplyLoading(false);
            setCanAbort(false);
            if (!tempHistory[index].context && tempHistory[index].thinking) {
              tempHistory[index].context = '对话发生错误，请稍后重试';
              tempHistory[index].thinking = false;
              setHistory([...tempHistory]);
            }
            resolve();
          },
          onClose: () => {
            setSseActive(false);
            setReplyLoading(false);
            setCanAbort(false);
            if (!tempHistory[index].context && tempHistory[index].thinking) {
              tempHistory[index].context = '对话发生错误，请稍后重试';
              tempHistory[index].thinking = false;
              setHistory([...tempHistory]);
            }
            resolve();
          },
          onError: message => {
            setSseActive(false);
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
    [history, modelValue, chat, appInfo, isPollingMode, stopPolling, sseActive],
  );

  useAsyncEffect(async () => {
    // 如果是默认小助手，不获取历史记录
    if (isChatDefault) {
      return;
    }
    const initMessage = getInitMessage();
    if (initMessage && initMessage.id === chatId) {
      return;
    }
    if(chatId) {
      await getHistory();
    }
  }, [chatId, getHistory, app_code]);

  useEffect(() => {
    if (isChatDefault) {
      order.current = 1;
      setHistory([]);
    }
  }, [isChatDefault]);
  
  const debouncedChat = useDebounceFn(handleChat, { wait: 500 });
  // 初始化消息处理
  useAsyncEffect(async () => {
    const initMessage = getInitMessage();
    if (initMessage && initMessage.id === chatId && appInfo) {
        
        let finalChatInParams = [...chatInParams];

        // Handle multiple file resources
        const fileResources = initMessage.resources || (initMessage.resource ? [initMessage.resource] : []);
        
if (fileResources.length > 0) {
            const resourceParamIndex = finalChatInParams.findIndex(p => p.param_type === 'resource');
            const resourceLayout = appInfo?.layout?.chat_in_layout?.find(item => item.param_type === 'resource');
            
            if (resourceParamIndex >= 0) {
                const newParams = [...finalChatInParams];
                newParams[resourceParamIndex] = {
                    ...newParams[resourceParamIndex],
                    param_value: JSON.stringify(fileResources)
                };
                finalChatInParams = newParams;
            } else {
                finalChatInParams = [
                    ...finalChatInParams,
                    {
                        param_type: 'resource',
                        param_value: JSON.stringify(fileResources),
                        sub_type: resourceLayout?.sub_type || 'common_file'
                    }
                ];
            }
            
 setResourceValue(fileResources);
        }
        
        // Handle skills - convert to chat_in_params format
        if (initMessage.skills && initMessage.skills.length > 0) {
          setSelectedSkills(initMessage.skills);
          
          // Add skills as chat_in_params
          const skillParams = initMessage.skills.map((skill: SelectedSkill) => ({
            param_type: 'resource',
            param_value: JSON.stringify(skill),
            sub_type: 'skill(derisk)',
          }));
          finalChatInParams = [...finalChatInParams, ...skillParams];
        }
        
        // Handle MCPs - convert to chat_in_params format
        if (initMessage.mcps && initMessage.mcps.length > 0) {
          const mcpParams = initMessage.mcps.map((mcp: any) => ({
            param_type: 'resource',
            param_value: JSON.stringify({
              mcp_code: mcp.id || mcp.uuid || mcp.mcp_code,
              name: mcp.name,
            }),
            sub_type: 'mcp(derisk)',
          }));
          finalChatInParams = [...finalChatInParams, ...mcpParams];
        }
        
if (initMessage.model) {
           setModelValue(initMessage.model);
           
           const modelLayout = appInfo?.layout?.chat_in_layout?.find(item => item.param_type === 'model');
           const existingModelParamIndex = finalChatInParams.findIndex(p => p.param_type === 'model');
           
           if (existingModelParamIndex >= 0) {
             const newParams = [...finalChatInParams];
             newParams[existingModelParamIndex] = {
               ...newParams[existingModelParamIndex],
               param_value: initMessage.model
             };
             finalChatInParams = newParams;
           } else if (modelLayout) {
             finalChatInParams = [
               ...finalChatInParams,
               {
                 param_type: 'model',
                 param_value: initMessage.model,
                 sub_type: modelLayout?.sub_type,
               }
             ];
           }
        }

         setChatInParams(finalChatInParams);

        // Build user_input with resources (same as unified-chat-input.tsx)
        let userContent: UserChatContent;
        if (fileResources.length > 0) {
          const messages: any[] = [...fileResources];
          if (initMessage.message?.trim()) {
            messages.push({ type: 'text', text: initMessage.message });
          }
          userContent = { role: 'user', content: messages };
        } else {
          userContent = initMessage.message;
        }

        debouncedChat.run(userContent, {
          app_code: appInfo?.app_code,
          ...(finalChatInParams?.length && {
            chat_in_params: finalChatInParams,
          }),
          ...(initMessage.model && { model_name: initMessage.model }),
        });
        refreshDialogList && await refreshDialogList();
        localStorage.removeItem(STORAGE_INIT_MESSAGE_KET);
    }
  }, [chatId, getInitMessage(), appInfo, chatInParams]);

  const contentRender = () => {
      if (isChatDefault) {
        return (
          <Content>
            <HomeChat />
          </Content>
        );
      }
      if (!Object.keys(appInfo).length) {
        return (
          <Content className='flex flex-col h-full'>
            <ChatPageSkeleton />
          </Content>
        );
      }
      return (
        <Content className='flex flex-col h-full min-h-0 overflow-hidden'>
          <ChatContentContainer ref={scrollRef} ctrl={ctrl} />
        </Content>
      );
  };

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
          currentConvSessionId,
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
          setAppInfo,
          setAgent,
          setCanAbort,
          setReplyLoading,
          setCurrentConvSessionId,
          handleChat,
          refreshDialogList,
          refreshHistory,
          refreshAppInfo,
          setHistory,
          isShowDetail,
          setIsShowDetail,
          setChatInParams,
          chatInParams,
          isPollingMode,
        }}
      >
        <Flex flex={1} className='min-h-0 overflow-hidden'>
          <Layout className='bg-gradient-light bg-cover bg-center dark:bg-gradient-dark w-full h-full'>
            <Layout className='bg-transparent h-full'>{contentRender()}</Layout>
          </Layout>
        </Flex>
      </ChatContentContext.Provider>
    </ContextMetricsProvider>
  )
}
