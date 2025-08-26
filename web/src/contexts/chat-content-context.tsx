import { ChartData, ChatHistoryResponse, IChatDialogueSchema, UserChatContent } from '@/types/chat';
import { IApp } from '@/types/app';
import { createContext} from 'react';

interface ChatContentProps {
  history: ChatHistoryResponse; // 会话记录列表
  replyLoading: boolean; // 对话回复loading
  scrollRef: React.RefObject<HTMLDivElement | null>; // 会话内容可滚动dom
  canAbort: boolean; // 是否能中断回复
  chartsData: ChartData[];
  agent: string;
  currentDialogue: IChatDialogueSchema; // 当前选择的会话
  appInfo: IApp;
  temperatureValue: number;
  maxNewTokensValue: number;
  resourceValue: Record<string, unknown>;
  modelValue: string;
  chatInParams: Array<{
    param_type: string;
    param_value: string;
    sub_type: string;
  }>;
  setModelValue: React.Dispatch<React.SetStateAction<string>>;
  setTemperatureValue: React.Dispatch<React.SetStateAction<number>>;
  setMaxNewTokensValue: React.Dispatch<React.SetStateAction<number>>;
  setResourceValue: React.Dispatch<React.SetStateAction<Record<string, unknown>>>;
  setChatInParams: (params: Array<{
    param_type: string;
    param_value: string;
    sub_type: string;
  }>) => void; // 设置聊天输入参数值
  setAppInfo: React.Dispatch<React.SetStateAction<IApp>>;
  setAgent: React.Dispatch<React.SetStateAction<string>>;
  setCanAbort: React.Dispatch<React.SetStateAction<boolean>>;
  setReplyLoading: React.Dispatch<React.SetStateAction<boolean>>;
  handleChat: (content: UserChatContent, data?: Record<string, unknown>) => Promise<void>; // 处理会话请求逻辑函数
  refreshDialogList: () => void;
  refreshHistory: () => void;
  refreshAppInfo: () => void;
  setHistory: React.Dispatch<React.SetStateAction<ChatHistoryResponse>>;
  isShowDetail?: boolean;
  setIsShowDetail?: React.Dispatch<React.SetStateAction<boolean>>;
  isDebug?: boolean;
}

export const ChatContentContext = createContext<ChatContentProps>({
  history: [],
  replyLoading: false,
  scrollRef: { current: null },
  canAbort: false,
  chartsData: [],
  agent: '',
  currentDialogue: {} as IChatDialogueSchema,
  appInfo: {} as IApp,
  temperatureValue: 0.5,
  maxNewTokensValue: 1024,
  resourceValue: {},
  chatInParams: [],
  setChatInParams: () => {},
  modelValue: '',
  setModelValue: () => {},
  setResourceValue: () => {},
  setTemperatureValue: () => {},
  setMaxNewTokensValue: () => {},
  setAppInfo: () => {},
  setAgent: () => {},
  setCanAbort: () => {},
  setReplyLoading: () => {},
  refreshDialogList: () => {},
  refreshHistory: () => {},
  refreshAppInfo: () => {},
  setHistory: () => {},
  handleChat: () => Promise.resolve(),
  isShowDetail: true,
  setIsShowDetail: () => {},
  isDebug: false,
});
