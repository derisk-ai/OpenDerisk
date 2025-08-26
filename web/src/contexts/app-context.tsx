import { createContext } from 'react';

interface AppContextProps {
  collapsed: boolean; // 是否折叠
  setCollapsed: React.Dispatch<React.SetStateAction<boolean>>; // 设置折叠
  appInfo?: any; // 应用信息
  setAppInfo?: React.Dispatch<React.SetStateAction<any>>; // 设置应用信息
  refreshAppInfo?: () => void; // 刷新应用信息
  refreshAppInfoLoading?: boolean;
  fetchUpdateApp: (arg: any) => void;
  fetchUpdateAppLoading?: boolean;
  setAssociationAgentModalOpen?: React.Dispatch<React.SetStateAction<boolean>>; // 设置关联Agent模态框打开状态
  setAssociationKnowledgeModalOpen?: React.Dispatch<React.SetStateAction<boolean>>; // 设置关联知识模态框打开状态
  setAssociationSkillModalOpen?: React.Dispatch<React.SetStateAction<boolean>>; // 设置关联技能模态框打开状态
  chatId?: string; // 会话ID
  setChatId?: React.Dispatch<React.SetStateAction<string>>; // 设置会话ID
  refetchVersionData?: () => void; // 刷新版本数据
  versionData?: any; // 版本数据
  queryAppInfo?: (appCode: string, configCode?: string) => void; // 查询应用信息
}

export const AppContext = createContext<AppContextProps>({
  collapsed: false,
  setCollapsed: () => {},
  appInfo: {},
  setAppInfo: () => {},
  refreshAppInfo: () => {},
  refreshAppInfoLoading: false,
  fetchUpdateApp: () => {},
  fetchUpdateAppLoading: false,
  setAssociationAgentModalOpen: () => {},
  setAssociationKnowledgeModalOpen: () => {},
  setAssociationSkillModalOpen: () => {},
  chatId: '',
  setChatId: () => {},
  refetchVersionData: () => {},
  versionData: {},
  queryAppInfo: () => {},
});
